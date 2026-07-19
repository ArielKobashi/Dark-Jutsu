@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "PG_SOURCE=%SHARE_ROOT%\instaladores\pgsql"
if not exist "%PG_SOURCE%\bin\pg_ctl.exe" set "PG_SOURCE=%USERPROFILE%\Desktop\aplicacoes code\pgsql"
set "PY_SOURCE=%SHARE_ROOT%\instaladores\WPy64-3.13.12.0"
set "PROJECT_SOURCE=%SHARE_ROOT%\pacote\Dark-Jutsu"
set "RUNTIME_ROOT=%LOCALAPPDATA%\DarkJutsu"
set "DESKTOP_DIR=%USERPROFILE%\Desktop"
for /f "usebackq delims=" %%D in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "[Environment]::GetFolderPath('Desktop')" 2^>nul`) do if not "%%D"=="" set "DESKTOP_DIR=%%D"
set "PG_HOME="
for %%G in ("%DESKTOP_DIR%\aplicacoes code\pgsql" "%DESKTOP_DIR%\pgsql" "%DESKTOP_DIR%\PostgreSQL\pgsql" "%DESKTOP_DIR%\PostgreSQL" "%DESKTOP_DIR%\Dark-Jutsu\PostgreSQL\pgsql" "%DESKTOP_DIR%\Dark-Jutsu\PostgreSQL") do (
  if not defined PG_HOME if exist "%%~fG\bin\pg_ctl.exe" if exist "%%~fG\share\postgres.bki" set "PG_HOME=%%~fG"
)
if not defined PG_HOME if exist "%DESKTOP_DIR%" (
  for /f "delims=" %%P in ('dir /s /b "%DESKTOP_DIR%\pg_ctl.exe" 2^>nul') do (
    if not defined PG_HOME (
      for %%D in ("%%~dpP..") do (
        if exist "%%~fD\share\postgres.bki" set "PG_HOME=%%~fD"
      )
    )
  )
)
if not defined PG_HOME set "PG_HOME=%RUNTIME_ROOT%\PostgreSQL\pgsql"
set "PG_BIN=%PG_HOME%\bin"
set "PGDATA=%RUNTIME_ROOT%\postgres-data"
echo "%PG_HOME%" | find /I "%DESKTOP_DIR%" >nul && set "PGDATA=%PG_HOME%\data"
set "APP_ROOT=%RUNTIME_ROOT%\Dark-Jutsu"
set "LOGDIR=%RUNTIME_ROOT%\logs"
set "PY_ROOT=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0"
set "LATEST_BACKUP="
set "CANDIDATE_LIST=%TEMP%\darkjutsu_user_restore_%RANDOM%.lst"

echo Dark-Jutsu - instalacao de servidor sem administrador
echo Destino: %RUNTIME_ROOT%
if not exist "%PG_SOURCE%\bin\pg_ctl.exe" echo ERRO: PostgreSQL portatil ausente em "%PG_SOURCE%". & exit /b 1
if not exist "%PG_SOURCE%\share\postgres.bki" echo ERRO: PostgreSQL portatil incompleto em "%PG_SOURCE%" ^(faltou share\postgres.bki^). & exit /b 1
if not exist "%PROJECT_SOURCE%\api\dark_jutsu_api.py" echo ERRO: pacote da API ausente. & exit /b 1
mkdir "%LOGDIR%" 2>nul
mkdir "%RUNTIME_ROOT%\PostgreSQL" 2>nul
mkdir "%APP_ROOT%" 2>nul
if not exist "%LOGDIR%" exit /b 1

if exist "%PG_BIN%\pg_ctl.exe" if exist "%PG_HOME%\share\postgres.bki" (
  echo PostgreSQL portatil existente detectado: %PG_HOME%
) else (
  echo PostgreSQL local ausente ou incompleto em "%PG_HOME%".
  echo Copiando/completando PostgreSQL portatil...
  robocopy "%PG_SOURCE%" "%PG_HOME%" /E /R:2 /W:2 /NFL /NDL /NP
  if errorlevel 8 exit /b 1
)
if not exist "%PG_HOME%\share\postgres.bki" (
  echo ERRO: PostgreSQL continuou incompleto em "%PG_HOME%" ^(faltou share\postgres.bki^).
  exit /b 1
)
if not exist "%PY_ROOT%\python\python.exe" (
  echo Copiando Python portatil...
  robocopy "%PY_SOURCE%" "%PY_ROOT%" /E /R:2 /W:2 /NFL /NDL /NP
  if errorlevel 8 exit /b 1
)
echo Copiando API...
robocopy "%PROJECT_SOURCE%" "%APP_ROOT%" /E /R:2 /W:2 /NFL /NDL /NP
if errorlevel 8 exit /b 1

if not exist "%PGDATA%\PG_VERSION" (
  echo Inicializando PostgreSQL local...
  "%PG_BIN%\initdb.exe" -D "%PGDATA%" -U postgres --auth=trust --encoding=UTF8
  if errorlevel 1 exit /b 1
  >>"%PGDATA%\pg_hba.conf" echo.
  >>"%PGDATA%\pg_hba.conf" echo host all all 192.168.0.0/16 md5
)
if exist "%PGDATA%\postgresql.conf" (
  >>"%PGDATA%\postgresql.conf" echo.
  >>"%PGDATA%\postgresql.conf" echo # Dark-Jutsu runtime config
  >>"%PGDATA%\postgresql.conf" echo port = 5433
  >>"%PGDATA%\postgresql.conf" echo listen_addresses = '*'
)
"%PG_BIN%\pg_isready.exe" -h 127.0.0.1 -p 5433 >nul 2>&1
if errorlevel 1 (
  "%PG_BIN%\pg_ctl.exe" -D "%PGDATA%" stop -m fast >nul 2>&1
  "%PG_BIN%\pg_ctl.exe" -D "%PGDATA%" -l "%LOGDIR%\postgres_runtime.log" start
  if errorlevel 1 exit /b 1
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$pg='%PG_BIN%\pg_isready.exe'; $deadline=(Get-Date).AddSeconds(45); do { & $pg -h 127.0.0.1 -p 5433 *> $null; if ($LASTEXITCODE -eq 0) { exit 0 }; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $deadline); exit 1"
  if errorlevel 1 (
    echo ERRO: PostgreSQL iniciou, mas nao respondeu na porta 5433.
    exit /b 1
  )
)

"%PG_BIN%\psql.exe" -h 127.0.0.1 -p 5433 -U postgres -d postgres -v ON_ERROR_STOP=1 -c "do $$ begin if not exists (select 1 from pg_roles where rolname = 'dark_jutsu') then create role dark_jutsu login password 'dark_jutsu_dev'; end if; end $$;"
if errorlevel 1 exit /b 1
"%PG_BIN%\psql.exe" -h 127.0.0.1 -p 5433 -U postgres -d postgres -At -c "select 'create database dark_jutsu owner dark_jutsu' where not exists (select from pg_database where datname='dark_jutsu')" | "%PG_BIN%\psql.exe" -h 127.0.0.1 -p 5433 -U postgres -d postgres
if errorlevel 1 exit /b 1

for /f "usebackq delims=" %%B in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%SHARE_ROOT%\backups' -Filter '*.backup' -ErrorAction SilentlyContinue ^| Where-Object Length -ge 1000000 ^| Sort-Object LastWriteTime -Descending ^| Select-Object -First 20 -ExpandProperty FullName"`) do (
  if not defined LATEST_BACKUP (
    "%PG_BIN%\pg_restore.exe" -l "%%B" > "%CANDIDATE_LIST%" 2>nul
    if not errorlevel 1 findstr /C:"TABLE DATA public users" "%CANDIDATE_LIST%" >nul && findstr /C:"TABLE DATA public inventory_items" "%CANDIDATE_LIST%" >nul && set "LATEST_BACKUP=%%B"
  )
)
if defined LATEST_BACKUP (
  echo Restaurando backup: !LATEST_BACKUP!
  "%PG_BIN%\pg_restore.exe" --exit-on-error -h 127.0.0.1 -p 5433 -U postgres -d dark_jutsu --clean --if-exists --no-owner "!LATEST_BACKUP!"
  if errorlevel 1 exit /b 1
) else echo AVISO: nenhum backup valido encontrado.
del "%CANDIDATE_LIST%" 2>nul

rem O pg_dump nao inclui associacoes globais de roles. Reaplica o acesso usado pela API
rem para que o login continue funcionando depois de restaurar ou trocar o servidor.
"%PG_BIN%\psql.exe" -h 127.0.0.1 -p 5433 -U postgres -d dark_jutsu -v ON_ERROR_STOP=1 -c "grant usage on schema public to dark_jutsu; grant select, insert, update, delete on all tables in schema public to dark_jutsu; grant usage, select, update on all sequences in schema public to dark_jutsu; grant execute on all functions in schema public to dark_jutsu;"
if errorlevel 1 exit /b 1
"%PG_BIN%\psql.exe" -h 127.0.0.1 -p 5433 -U postgres -d dark_jutsu -v ON_ERROR_STOP=1 -c "do $$ begin if exists (select 1 from pg_roles where rolname='dark_jutsu_service') then grant dark_jutsu_service to dark_jutsu; alter role dark_jutsu inherit; end if; end $$;"
if errorlevel 1 exit /b 1

call "%~dp0instalar_atualizar_guardiao_monitor_darkjutsu.bat"
if errorlevel 1 exit /b 1
echo OK: servidor instalado sem administrador em "%RUNTIME_ROOT%".
exit /b 0
