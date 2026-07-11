@echo off
setlocal EnableExtensions

set "PG_BIN=C:\DarkJutsu\PostgreSQL\pgsql\bin"
if not exist "%PG_BIN%\pg_restore.exe" set "PG_BIN=%USERPROFILE%\Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql\bin"
set "PGHOST=127.0.0.1"
set "PGPORT=5433"
set "BACKUP_DIR=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\backups"
set "TEST_DB=dark_jutsu_restore_test"
set "DB_OWNER=dark_jutsu"
set "LOGDIR=C:\DarkJutsu\logs"
set "LOGFILE=%LOGDIR%\postgres_restore_test.log"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

if not exist "%PG_BIN%\pg_restore.exe" (
  echo ERRO: pg_restore.exe nao encontrado em %PG_BIN%.
  exit /b 1
)

for /f "usebackq delims=" %%B in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%BACKUP_DIR%' -Filter 'darkjutsu_backup_*.backup' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"`) do set "LATEST_BACKUP=%%B"

if "%LATEST_BACKUP%"=="" (
  echo ERRO: nenhum backup encontrado em %BACKUP_DIR%.
  exit /b 1
)

echo ================================================== >> "%LOGFILE%"
echo [%date% %time%] Testando restore em banco temporario: %LATEST_BACKUP% >> "%LOGFILE%"

"%PG_BIN%\dropdb.exe" -h "%PGHOST%" -p "%PGPORT%" -U postgres --if-exists "%TEST_DB%" >> "%LOGFILE%" 2>&1
if errorlevel 1 exit /b 1

"%PG_BIN%\createdb.exe" -h "%PGHOST%" -p "%PGPORT%" -U postgres -O "%DB_OWNER%" "%TEST_DB%" >> "%LOGFILE%" 2>&1
if errorlevel 1 exit /b 1

"%PG_BIN%\pg_restore.exe" -h "%PGHOST%" -p "%PGPORT%" -U postgres -d "%TEST_DB%" --no-owner "%LATEST_BACKUP%" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo ERRO: restore de teste falhou. Veja %LOGFILE%.
  exit /b 1
)

"%PG_BIN%\psql.exe" -h "%PGHOST%" -p "%PGPORT%" -U postgres -d "%TEST_DB%" -v ON_ERROR_STOP=1 -c "select count(*) as users from users;" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo ERRO: banco restaurado nao respondeu consulta basica. Veja %LOGFILE%.
  exit /b 1
)

"%PG_BIN%\dropdb.exe" -h "%PGHOST%" -p "%PGPORT%" -U postgres --if-exists "%TEST_DB%" >> "%LOGFILE%" 2>&1

echo [%date% %time%] Restore de teste OK. >> "%LOGFILE%"
echo Restore de teste OK: %LATEST_BACKUP%
exit /b 0
