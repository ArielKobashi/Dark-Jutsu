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
set "LOCK_MAX_AGE_MINUTES=20"
set "VERSION_FILE=%SHARE_ROOT%\versao_github_atual.txt"
set "EVENT_LOGGER=%SHARE_ROOT%\scripts\registrar_evento_servidor_darkjutsu.bat"
set "NEW_COMMIT="
set "OLD_COMMIT="
set "REMOTE_COMMIT="
set "FORCE_UPDATE=0"
set "LOCAL_API_WAS_ON=0"
set "LOCAL_IP="

if /I "%~1"=="--force" set "FORCE_UPDATE=1"

call :prepare_local_paths
if errorlevel 1 exit /b 1

call :log "=================================================="
call :log "Inicio atualizacao GitHub. Usuario=%USERNAME% Maquina=%COMPUTERNAME%"

ipconfig | findstr /C:"192.168.5.44" >nul 2>&1
if %errorlevel%==0 set "LOCAL_IP=192.168.5.44"
if "%LOCAL_IP%"=="" (
  ipconfig | findstr /C:"192.168.5.38" >nul 2>&1
  if !errorlevel!==0 set "LOCAL_IP=192.168.5.38"
)

if not exist "%SHARE_ROOT%\app" (
  call :log "FALHOU: servidor de arquivos nao acessivel: %SHARE_ROOT%"
  exit /b 1
)

call :acquire_lock
if errorlevel 1 exit /b 0

where git.exe >nul 2>&1
if errorlevel 1 (
  if "%LOCAL_IP%"=="192.168.5.38" (
    call :log "AVISO: git.exe nao encontrado na reserva. Principal pode continuar responsavel por atualizar."
    call :event_once AVISO ATUALIZACAO "Git nao encontrado na reserva; principal deve puxar atualizacoes do GitHub. Se quiser reserva atualizando tambem, instale/copiar PortableGit."
    call :unlock
    exit /b 0
  )
  call :log "FALHOU: git.exe nao encontrado nesta maquina principal."
  call :event_once ERRO ATUALIZACAO "Git nao encontrado no principal; servidor nao consegue puxar atualizacoes do GitHub."
  call :unlock
  exit /b 1
)
del "%SHARE_ROOT%\atualizacao-github-sem-git-%COMPUTERNAME%.txt" >nul 2>&1

for /f "tokens=1" %%C in ('git ls-remote "%REPO_URL%" "refs/heads/%BRANCH%" 2^>nul') do set "REMOTE_COMMIT=%%C"
if not defined REMOTE_COMMIT (
  call :log "FALHOU: nao consegui consultar GitHub rapidamente."
  call :event ERRO ATUALIZACAO "Nao consegui consultar GitHub. Verifique internet, DNS, proxy ou permissao do Git."
  call :unlock
  exit /b 1
)
if exist "%VERSION_FILE%" set /p OLD_COMMIT=<"%VERSION_FILE%"
if /I "%REMOTE_COMMIT%"=="%OLD_COMMIT%" (
  call :log "Sem mudanca no GitHub. Versao atual: %REMOTE_COMMIT%"
  call :unlock
  exit /b 0
)

if not exist "%REPO_DIR%\.git" (
  call :log "Clone inicial em %REPO_DIR%"
  if exist "%REPO_DIR%" rmdir /S /Q "%REPO_DIR%" >nul 2>&1
  git clone --branch "%BRANCH%" "%REPO_URL%" "%REPO_DIR%" >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    call :log "FALHOU: git clone nao concluiu."
    call :event ERRO ATUALIZACAO "Falha no git clone do GitHub."
    call :unlock
    exit /b 1
  )
) else (
  call :log "Atualizando clone local."
  git -C "%REPO_DIR%" remote set-url origin "%REPO_URL%" >> "%LOGFILE%" 2>&1
  git -C "%REPO_DIR%" fetch origin "%BRANCH%" >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    call :log "FALHOU: git fetch nao concluiu."
    call :event ERRO ATUALIZACAO "Falha no git fetch do GitHub."
    call :unlock
    exit /b 1
  )
  git -C "%REPO_DIR%" reset --hard "origin/%BRANCH%" >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    call :log "FALHOU: git reset nao concluiu."
    call :event ERRO ATUALIZACAO "Falha ao aplicar versao baixada do GitHub no clone local."
    call :unlock
    exit /b 1
  )
)

for /f %%C in ('git -C "%REPO_DIR%" rev-parse HEAD 2^>nul') do set "NEW_COMMIT=%%C"
if not defined NEW_COMMIT (
  call :log "FALHOU: clone local nao possui commit valido em %REPO_DIR%."
  call :event ERRO ATUALIZACAO "Clone local GitHub sem commit valido; atualizacao abortada."
  call :unlock
  exit /b 1
)

if /I "%NEW_COMMIT%"=="%OLD_COMMIT%" (
  call :log "Sem mudanca. Versao ja aplicada: %NEW_COMMIT%"
  call :unlock
  exit /b 0
)

call :log "Nova versao detectada: %NEW_COMMIT%"
if "%OLD_COMMIT%"=="" call :log "Arquivo de versao ausente; publicando commit atual do GitHub como base inicial."
call :health_local
if "%errorlevel%"=="0" set "LOCAL_API_WAS_ON=1"
call :publish
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  call :log "FALHOU: publicacao retornou codigo %RC%."
  call :event ERRO ATUALIZACAO "Falha ao publicar atualizacao no fileserver. Codigo=%RC%."
  call :unlock
  exit /b %RC%
)

>"%VERSION_FILE%" echo %NEW_COMMIT%
call :log "Versao publicada no servidor de arquivos: %NEW_COMMIT%"
call :event OK ATUALIZACAO "Servidor atualizado pelo GitHub. Commit=%NEW_COMMIT%."

if exist "%SHARE_SCRIPTS%\instalar_atualizar_guardiao_monitor_darkjutsu.bat" (
  call :log "Reinstalando guardiao/monitor nesta maquina para pegar scripts novos."
  call "%SHARE_SCRIPTS%\instalar_atualizar_guardiao_monitor_darkjutsu.bat" >> "%LOGFILE%" 2>&1
)
if "%LOCAL_API_WAS_ON%"=="1" (
  call :log "API local estava ativa; reiniciando para carregar versao nova."
  call "%SHARE_SCRIPTS%\parar_api_darkjutsu.bat" "atualizar_github" >> "%LOGFILE%" 2>&1
  call "%SHARE_SCRIPTS%\assumir_servidor_darkjutsu.bat" >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    call :log "ERRO: API nao reiniciou corretamente apos atualizacao."
    call :event ERRO ATUALIZACAO "API local nao reiniciou corretamente apos atualizacao GitHub."
  ) else (
    call :event OK ATUALIZACAO "API local reiniciada apos atualizacao GitHub."
  )
)

call :unlock
exit /b 0

:prepare_local_paths
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
if not exist "%WORK_ROOT%" mkdir "%WORK_ROOT%" 2>nul
if not exist "%LOGDIR%" (
  set "LOGDIR=%LOCALAPPDATA%\DarkJutsu\logs"
  set "LOGFILE=%LOCALAPPDATA%\DarkJutsu\logs\atualizacao_github.log"
)
if not exist "%WORK_ROOT%" (
  set "WORK_ROOT=%LOCALAPPDATA%\DarkJutsu\github-sync"
  set "REPO_DIR=%LOCALAPPDATA%\DarkJutsu\github-sync\Dark-Jutsu"
)
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
if not exist "%WORK_ROOT%" mkdir "%WORK_ROOT%" 2>nul
if not exist "%LOGDIR%" (
  echo FALHOU: nao consegui criar pasta de logs em C:\DarkJutsu nem em %%LOCALAPPDATA%%\DarkJutsu.
  exit /b 1
)
if not exist "%WORK_ROOT%" (
  echo FALHOU: nao consegui criar pasta de clone em C:\DarkJutsu nem em %%LOCALAPPDATA%%\DarkJutsu.
  exit /b 1
)
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
rmdir /S /Q "%LOCKDIR%" >nul 2>&1
exit /b 0

:acquire_lock
if exist "%LOCKDIR%" (
  for %%L in ("%LOCKDIR%") do set "LOCK_WRITE=%%~tL"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=$env:LOCKDIR; $max=[int]$env:LOCK_MAX_AGE_MINUTES; if(Test-Path -LiteralPath $p){ $age=(New-TimeSpan -Start (Get-Item -LiteralPath $p).LastWriteTime -End (Get-Date)).TotalMinutes; if($age -ge $max){ exit 0 } }; exit 1" >nul 2>&1
  if not errorlevel 1 (
    call :log "Lock antigo detectado em %LOCKDIR% LastWrite=%LOCK_WRITE%. Removendo para destravar atualizacao."
    rmdir /S /Q "%LOCKDIR%" >nul 2>&1
  )
)
mkdir "%LOCKDIR%" >nul 2>&1
if errorlevel 1 (
  call :log "Outro atualizador ja esta rodando. Saindo."
  exit /b 1
)
>"%LOCKDIR%\owner.txt" echo %date% %time% usuario=%USERNAME% maquina=%COMPUTERNAME% pid=%PROCESSID%
exit /b 0

:log
echo [%date% %time%] %~1
>>"%LOGFILE%" echo [%date% %time%] %~1
exit /b 0

:event
if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "%~1" "%~2" "%~3"
exit /b 0

:event_once
set "MARKER=%SHARE_ROOT%\atualizacao-github-sem-git-%COMPUTERNAME%.txt"
if not exist "%MARKER%" (
  >"%MARKER%" echo %date% %time% %~1 %~2 %~3
  call :event "%~1" "%~2" "%~3"
)
exit /b 0

:health_local
curl -fsS --max-time 2 "http://127.0.0.1:8765/health" >nul 2>&1
exit /b %errorlevel%
