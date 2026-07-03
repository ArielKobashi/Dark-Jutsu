@echo off
setlocal EnableExtensions

set "PG_BIN=C:\DarkJutsu\PostgreSQL\pgsql\bin"
set "PGHOST=127.0.0.1"
set "PGPORT=5433"
set "DB_NAME=dark_jutsu"
set "DB_OWNER=dark_jutsu"
set "BACKUP_DIR=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\backups"
set "LOGDIR=C:\DarkJutsu\logs"
set "LOGFILE=%LOGDIR%\postgres_restore_inativo.log"
set "STATEFILE=%LOGDIR%\ultimo_backup_restaurado.txt"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo ================================================== >> "%LOGFILE%"
echo [%date% %time%] Verificando backup para servidor inativo... >> "%LOGFILE%"

netstat -ano -p tcp | findstr /R /C:":8765 .*LISTENING" >nul
if %errorlevel%==0 (
    echo [%date% %time%] API local esta ativa. Restauracao ignorada para nao sobrescrever servidor em uso. >> "%LOGFILE%"
    exit /b 0
)

for /f "usebackq delims=" %%B in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%BACKUP_DIR%' -Filter 'darkjutsu_backup_*.backup' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"`) do set "LATEST_BACKUP=%%B"

if "%LATEST_BACKUP%"=="" (
    echo [%date% %time%] Nenhum backup encontrado em %BACKUP_DIR%. >> "%LOGFILE%"
    exit /b 0
)

set "LAST_RESTORED="
if exist "%STATEFILE%" set /p LAST_RESTORED=<"%STATEFILE%"
if /I "%LAST_RESTORED%"=="%LATEST_BACKUP%" (
    echo [%date% %time%] Backup mais recente ja foi restaurado: %LATEST_BACKUP% >> "%LOGFILE%"
    exit /b 0
)

if not exist "%PG_BIN%\pg_restore.exe" (
    echo [%date% %time%] ERRO: pg_restore.exe nao encontrado em %PG_BIN%. >> "%LOGFILE%"
    exit /b 1
)

call "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\iniciar_postgres_darkjutsu.bat" >> "%LOGFILE%" 2>&1
if errorlevel 1 exit /b 1

echo [%date% %time%] Restaurando backup: %LATEST_BACKUP% >> "%LOGFILE%"

"%PG_BIN%\psql.exe" -h "%PGHOST%" -p "%PGPORT%" -U postgres -d postgres -v ON_ERROR_STOP=1 -c "select pg_terminate_backend(pid) from pg_stat_activity where datname = '%DB_NAME%' and pid <> pg_backend_pid();" >> "%LOGFILE%" 2>&1
"%PG_BIN%\dropdb.exe" -h "%PGHOST%" -p "%PGPORT%" -U postgres --if-exists "%DB_NAME%" >> "%LOGFILE%" 2>&1
if errorlevel 1 exit /b 1
"%PG_BIN%\createdb.exe" -h "%PGHOST%" -p "%PGPORT%" -U postgres -O "%DB_OWNER%" "%DB_NAME%" >> "%LOGFILE%" 2>&1
if errorlevel 1 exit /b 1
"%PG_BIN%\pg_restore.exe" -h "%PGHOST%" -p "%PGPORT%" -U postgres -d "%DB_NAME%" --no-owner "%LATEST_BACKUP%" >> "%LOGFILE%" 2>&1
if errorlevel 1 exit /b 1

echo %LATEST_BACKUP%>"%STATEFILE%"
echo [%date% %time%] Backup restaurado com sucesso. >> "%LOGFILE%"
exit /b 0
