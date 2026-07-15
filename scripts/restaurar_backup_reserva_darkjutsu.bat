@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "PG_BIN=C:\DarkJutsu\PostgreSQL\pgsql\bin"
set "PGHOST=127.0.0.1"
set "PGPORT=5433"
set "DB_NAME=dark_jutsu"
set "DB_OWNER=dark_jutsu"
set "BACKUP_DIR=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\backups"
set "LOGDIR=C:\DarkJutsu\logs"
set "LOGFILE=%LOGDIR%\postgres_restore_inativo.log"
set "STATEFILE=%LOGDIR%\ultimo_backup_restaurado.txt"
set "CANDIDATE_LIST=%LOGDIR%\restore_candidate.lst"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo ================================================== >> "%LOGFILE%"
echo [%date% %time%] Verificando backup para servidor inativo... >> "%LOGFILE%"

netstat -ano -p tcp | findstr /R /C:":8765 .*LISTENING" >nul
if %errorlevel%==0 (
    echo [%date% %time%] API local esta ativa. Restauracao ignorada para nao sobrescrever servidor em uso. >> "%LOGFILE%"
    exit /b 0
)

if not exist "%PG_BIN%\pg_restore.exe" (
    echo [%date% %time%] ERRO: pg_restore.exe nao encontrado em %PG_BIN%. >> "%LOGFILE%"
    exit /b 1
)

set "LATEST_BACKUP="
for /f "usebackq delims=" %%B in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%BACKUP_DIR%' -Filter 'darkjutsu_backup_*.backup' | Where-Object { $_.Length -ge 1000000 } | Sort-Object LastWriteTime -Descending | Select-Object -First 20 -ExpandProperty FullName"`) do (
    if not defined LATEST_BACKUP (
        echo [%date% %time%] Validando candidato de restore: %%B >> "%LOGFILE%"
        "%PG_BIN%\pg_restore.exe" -l "%%B" > "%CANDIDATE_LIST%" 2>> "%LOGFILE%"
        if not errorlevel 1 (
            findstr /C:"TABLE DATA public users" "%CANDIDATE_LIST%" >nul
            if not errorlevel 1 (
                findstr /C:"TABLE DATA public inventory_items" "%CANDIDATE_LIST%" >nul
                if not errorlevel 1 set "LATEST_BACKUP=%%B"
            )
        )
    )
)

if "%LATEST_BACKUP%"=="" (
    echo [%date% %time%] Nenhum backup valido encontrado em %BACKUP_DIR%. Arquivos pequenos/truncados foram ignorados. >> "%LOGFILE%"
    exit /b 0
)

set "LAST_RESTORED="
if exist "%STATEFILE%" set /p LAST_RESTORED=<"%STATEFILE%"
if /I "%LAST_RESTORED%"=="%LATEST_BACKUP%" (
    echo [%date% %time%] Backup mais recente ja foi restaurado: %LATEST_BACKUP% >> "%LOGFILE%"
    exit /b 0
)

call "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\iniciar_postgres_darkjutsu.bat" >> "%LOGFILE%" 2>&1
if errorlevel 1 exit /b 1

echo [%date% %time%] Restaurando backup: %LATEST_BACKUP% >> "%LOGFILE%"

"%PG_BIN%\psql.exe" -h "%PGHOST%" -p "%PGPORT%" -U postgres -d postgres -v ON_ERROR_STOP=1 -c "select pg_terminate_backend(pid) from pg_stat_activity where datname = '%DB_NAME%' and pid <> pg_backend_pid();" >> "%LOGFILE%" 2>&1
"%PG_BIN%\dropdb.exe" -h "%PGHOST%" -p "%PGPORT%" -U postgres --if-exists "%DB_NAME%" >> "%LOGFILE%" 2>&1
if errorlevel 1 exit /b 1
"%PG_BIN%\createdb.exe" -h "%PGHOST%" -p "%PGPORT%" -U postgres -O "%DB_OWNER%" "%DB_NAME%" >> "%LOGFILE%" 2>&1
if errorlevel 1 exit /b 1
"%PG_BIN%\pg_restore.exe" --exit-on-error -h "%PGHOST%" -p "%PGPORT%" -U postgres -d "%DB_NAME%" --no-owner "%LATEST_BACKUP%" >> "%LOGFILE%" 2>&1
if errorlevel 1 exit /b 1

"%PG_BIN%\psql.exe" -h "%PGHOST%" -p "%PGPORT%" -U postgres -d "%DB_NAME%" -v ON_ERROR_STOP=1 -c "grant usage, create on schema public to dark_jutsu; grant select, insert, update, delete on all tables in schema public to dark_jutsu; grant usage, select, update on all sequences in schema public to dark_jutsu; grant execute on all functions in schema public to dark_jutsu;" >> "%LOGFILE%" 2>&1
if errorlevel 1 exit /b 1

"%PG_BIN%\psql.exe" -h "%PGHOST%" -p "%PGPORT%" -U postgres -d "%DB_NAME%" -v ON_ERROR_STOP=1 -c "set app.role='service'; select count(*) as users from users; select count(*) as inventory_items from inventory_items;" >> "%LOGFILE%" 2>&1
if errorlevel 1 exit /b 1

echo %LATEST_BACKUP%>"%STATEFILE%"
echo [%date% %time%] Backup restaurado com sucesso. >> "%LOGFILE%"
exit /b 0
