@echo off
setlocal EnableExtensions

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "PG_SOURCE=%SHARE_ROOT%\instaladores\pgsql"
set "PY_SOURCE=%SHARE_ROOT%\instaladores\WPy64-3.13.12.0"
set "PROJECT_SOURCE=%SHARE_ROOT%\pacote\Dark-Jutsu"
set "PG_HOME=C:\DarkJutsu\PostgreSQL\pgsql"
set "PG_BIN=%PG_HOME%\bin"
set "PGDATA=C:\DarkJutsu\postgres-data"
set "LOGDIR=C:\DarkJutsu\logs"
set "APP_ROOT=C:\Users\%USERNAME%\Desktop\Dark-Jutsu"
set "PY_ROOT=C:\Users\%USERNAME%\Desktop\aplicacoes code"

echo ==================================================
echo Configurando servidor reserva Dark-Jutsu nesta maquina
echo ==================================================
echo.

if not exist "%PG_SOURCE%\bin\pg_ctl.exe" (
    echo ERRO: PostgreSQL portable nao encontrado em:
    echo %PG_SOURCE%
    echo.
    echo Copie a pasta pgsql para %SHARE_ROOT%\instaladores antes de rodar este instalador.
    exit /b 1
)

if not exist "%PROJECT_SOURCE%\api\dark_jutsu_api.py" (
    echo ERRO: pacote Dark-Jutsu nao encontrado em:
    echo %PROJECT_SOURCE%
    exit /b 1
)

if not exist "%PY_SOURCE%\python\python.exe" (
    echo ERRO: Python portable nao encontrado em:
    echo %PY_SOURCE%
    exit /b 1
)

mkdir "C:\DarkJutsu\PostgreSQL" 2>nul
mkdir "%LOGDIR%" 2>nul

if not exist "%PG_BIN%\pg_ctl.exe" (
    echo Copiando PostgreSQL portable para %PG_HOME%...
    xcopy "%PG_SOURCE%" "%PG_HOME%\" /E /I /Y
    if errorlevel 1 exit /b 1
) else (
    echo PostgreSQL portable ja existe em %PG_HOME%.
)

if not exist "%PY_ROOT%\WPy64-3.13.12.0\python\python.exe" (
    echo Copiando Python portable para %PY_ROOT%...
    mkdir "%PY_ROOT%" 2>nul
    xcopy "%PY_SOURCE%" "%PY_ROOT%\WPy64-3.13.12.0\" /E /I /Y
    if errorlevel 1 exit /b 1
) else (
    echo Python portable ja existe em %PY_ROOT%\WPy64-3.13.12.0.
)

call "%SHARE_ROOT%\scripts\corrigir_python_reserva_darkjutsu.bat"
if errorlevel 1 exit /b 1

echo Copiando pacote Dark-Jutsu para %APP_ROOT%...
mkdir "%APP_ROOT%" 2>nul
xcopy "%PROJECT_SOURCE%" "%APP_ROOT%\" /E /I /Y
if errorlevel 1 exit /b 1

if not exist "%PGDATA%\PG_VERSION" (
    echo Inicializando cluster PostgreSQL em %PGDATA%...
    "%PG_BIN%\initdb.exe" -D "%PGDATA%" -U postgres --auth=trust --encoding=UTF8
    if errorlevel 1 exit /b 1

    echo.>> "%PGDATA%\postgresql.conf"
    echo # Dark-Jutsu portable local>> "%PGDATA%\postgresql.conf"
    echo port = 5433>> "%PGDATA%\postgresql.conf"
    echo listen_addresses = '*'>> "%PGDATA%\postgresql.conf"
    echo.>> "%PGDATA%\pg_hba.conf"
    echo # Dark-Jutsu LAN access>> "%PGDATA%\pg_hba.conf"
    echo host    all             all             192.168.0.0/16            md5>> "%PGDATA%\pg_hba.conf"
) else (
    echo Cluster PostgreSQL ja existe em %PGDATA%.
)

echo Iniciando PostgreSQL...
call "%SHARE_ROOT%\scripts\iniciar_postgres_darkjutsu.bat"
if errorlevel 1 exit /b 1

echo Criando usuario e banco, se necessario...
"%PG_BIN%\psql.exe" -h 127.0.0.1 -p 5433 -U postgres -d postgres -v ON_ERROR_STOP=1 -c "do $$ begin if not exists (select 1 from pg_roles where rolname = 'dark_jutsu') then create role dark_jutsu login password 'dark_jutsu_dev'; end if; end $$;"
if errorlevel 1 exit /b 1
"%PG_BIN%\psql.exe" -h 127.0.0.1 -p 5433 -U postgres -d postgres -v ON_ERROR_STOP=1 -c "select 'create database dark_jutsu owner dark_jutsu' where not exists (select from pg_database where datname = 'dark_jutsu')" -At | "%PG_BIN%\psql.exe" -h 127.0.0.1 -p 5433 -U postgres -d postgres
if errorlevel 1 exit /b 1

echo Localizando backup mais recente...
for /f "usebackq delims=" %%B in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%SHARE_ROOT%\backups' -Filter '*.backup' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"`) do set "LATEST_BACKUP=%%B"

if "%LATEST_BACKUP%"=="" (
    echo AVISO: nenhum backup .backup encontrado em %SHARE_ROOT%\backups.
    echo O banco foi criado, mas nao foi restaurado.
) else (
    echo Restaurando backup:
    echo %LATEST_BACKUP%
    "%PG_BIN%\pg_restore.exe" -h 127.0.0.1 -p 5433 -U postgres -d dark_jutsu --clean --if-exists --no-owner "%LATEST_BACKUP%"
    if errorlevel 1 exit /b 1
)

echo Instalando atalhos de inicializacao para este usuario...
call "%SHARE_ROOT%\scripts\instalar_atualizar_guardiao_monitor_darkjutsu.bat"

echo Iniciando API Dark-Jutsu...
call "%SHARE_ROOT%\scripts\iniciar_servidor_se_necessario_darkjutsu.bat"

echo.
echo ==================================================
echo Servidor reserva Dark-Jutsu configurado.
echo Teste nesta maquina:
echo http://127.0.0.1:8765/health
echo.
echo Teste em outro PC:
echo http://IP_DESTA_MAQUINA:8765/health
echo ==================================================
pause
