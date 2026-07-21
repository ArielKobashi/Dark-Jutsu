@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "PG_BIN=%DARK_JUTSU_PG_BIN%"
if not exist "%PG_BIN%\pg_dump.exe" set "PG_BIN=C:\DarkJutsu\PostgreSQL\pgsql\bin"
if not exist "%PG_BIN%\pg_dump.exe" set "PG_BIN=%LOCALAPPDATA%\DarkJutsu\PostgreSQL\pgsql\bin"
if not exist "%PG_BIN%\pg_dump.exe" set "PG_BIN=%USERPROFILE%\Desktop\aplicacoes code\pgsql\bin"
if not exist "%PG_BIN%\pg_dump.exe" set "PG_BIN=%USERPROFILE%\Desktop\pgsql\bin"
if not exist "%PG_BIN%\pg_dump.exe" set "PG_BIN=%USERPROFILE%\Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql\bin"
set "PGHOST=127.0.0.1"
set "PGPORT=5433"
set "PGUSER=postgres"
set "PGDATABASE=dark_jutsu"
set "API_URL=http://127.0.0.1:8765/health"
set "BACKUP_DIR=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\backups"
set "STAGING_DIR=C:\DarkJutsu\backup-staging"
set "LOGDIR=C:\DarkJutsu\logs"
set "LOGFILE=%LOGDIR%\postgres_backup.log"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"
if not exist "%STAGING_DIR%" mkdir "%STAGING_DIR%"

for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"`) do set "STAMP=%%T"
set "BACKUP_FILE=%BACKUP_DIR%\darkjutsu_backup_%STAMP%.backup"
set "TEMP_BACKUP_FILE=%STAGING_DIR%\darkjutsu_backup_%STAMP%.backup.tmp"
set "LIST_FILE=%STAGING_DIR%\darkjutsu_backup_%STAMP%.lst"

echo ================================================== >> "%LOGFILE%"
echo [%date% %time%] Iniciando backup Dark-Jutsu... >> "%LOGFILE%"

curl.exe -fsS --max-time 3 "%API_URL%" >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] API local nao esta ativa. Backup ignorado; esta maquina nao e o servidor em uso. >> "%LOGFILE%"
    exit /b 0
)

if not exist "%PG_BIN%\pg_dump.exe" (
    echo [%date% %time%] ERRO: pg_dump.exe nao encontrado em %PG_BIN%. >> "%LOGFILE%"
    exit /b 1
)

"%PG_BIN%\pg_isready.exe" -h "%PGHOST%" -p "%PGPORT%" -U "%PGUSER%" -d "%PGDATABASE%" >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERRO: PostgreSQL nao esta pronto em %PGHOST%:%PGPORT%. >> "%LOGFILE%"
    exit /b 1
)

if exist "%TEMP_BACKUP_FILE%" del "%TEMP_BACKUP_FILE%" >nul 2>&1
if exist "%LIST_FILE%" del "%LIST_FILE%" >nul 2>&1

"%PG_BIN%\pg_dump.exe" -h "%PGHOST%" -p "%PGPORT%" -U "%PGUSER%" -d "%PGDATABASE%" -F c -f "%TEMP_BACKUP_FILE%" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERRO: falha ao gerar backup temporario. Arquivo nao sera publicado. >> "%LOGFILE%"
    if exist "%TEMP_BACKUP_FILE%" del "%TEMP_BACKUP_FILE%" >nul 2>&1
    exit /b 1
)

for %%S in ("%TEMP_BACKUP_FILE%") do set "BACKUP_SIZE=%%~zS"
if "!BACKUP_SIZE!"=="" set "BACKUP_SIZE=0"
if !BACKUP_SIZE! LSS 1000000 (
    echo [%date% %time%] ERRO: backup temporario pequeno demais: !BACKUP_SIZE! bytes. Arquivo nao sera publicado. >> "%LOGFILE%"
    if exist "%TEMP_BACKUP_FILE%" del "%TEMP_BACKUP_FILE%" >nul 2>&1
    exit /b 1
)

"%PG_BIN%\pg_restore.exe" -l "%TEMP_BACKUP_FILE%" > "%LIST_FILE%" 2>> "%LOGFILE%"
if errorlevel 1 (
    echo [%date% %time%] ERRO: backup temporario falhou na validacao pg_restore -l. Arquivo nao sera publicado. >> "%LOGFILE%"
    if exist "%TEMP_BACKUP_FILE%" del "%TEMP_BACKUP_FILE%" >nul 2>&1
    exit /b 1
)
findstr /C:"TABLE DATA public users" "%LIST_FILE%" >nul
if errorlevel 1 (
    echo [%date% %time%] ERRO: backup temporario nao contem dados da tabela users. Arquivo nao sera publicado. >> "%LOGFILE%"
    if exist "%TEMP_BACKUP_FILE%" del "%TEMP_BACKUP_FILE%" >nul 2>&1
    exit /b 1
)
findstr /C:"TABLE DATA public inventory_items" "%LIST_FILE%" >nul
if errorlevel 1 (
    echo [%date% %time%] ERRO: backup temporario nao contem dados da tabela inventory_items. Arquivo nao sera publicado. >> "%LOGFILE%"
    if exist "%TEMP_BACKUP_FILE%" del "%TEMP_BACKUP_FILE%" >nul 2>&1
    exit /b 1
)

copy /Y "%TEMP_BACKUP_FILE%" "%BACKUP_FILE%" >nul
if errorlevel 1 (
    echo [%date% %time%] ERRO: falha ao publicar backup validado no fileserver. >> "%LOGFILE%"
    exit /b 1
)

"%PG_BIN%\pg_restore.exe" -l "%BACKUP_FILE%" >nul 2>> "%LOGFILE%"
if errorlevel 1 (
    echo [%date% %time%] ERRO: backup publicado nao passou validacao final. Removendo arquivo ruim. >> "%LOGFILE%"
    del "%BACKUP_FILE%" >nul 2>&1
    exit /b 1
)

echo [%date% %time%] Backup validado e publicado pela maquina ativa: %BACKUP_FILE% (!BACKUP_SIZE! bytes) >> "%LOGFILE%"
del "%TEMP_BACKUP_FILE%" >nul 2>&1
del "%LIST_FILE%" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%BACKUP_DIR%' -Filter 'darkjutsu_backup_*.backup' | Sort-Object LastWriteTime -Descending | Select-Object -Skip 72 | Remove-Item -Force" >> "%LOGFILE%" 2>&1

exit /b 0
