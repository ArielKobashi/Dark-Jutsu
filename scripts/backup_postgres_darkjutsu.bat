@echo off
setlocal EnableExtensions

set "PG_BIN=C:\DarkJutsu\PostgreSQL\pgsql\bin"
if not exist "%PG_BIN%\pg_dump.exe" set "PG_BIN=%USERPROFILE%\Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql\bin"
set "PGHOST=127.0.0.1"
set "PGPORT=5433"
set "PGUSER=dark_jutsu"
set "PGDATABASE=dark_jutsu"
set "API_URL=http://127.0.0.1:8765/health"
set "BACKUP_DIR=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\backups"
set "LOGDIR=C:\DarkJutsu\logs"
set "LOGFILE=%LOGDIR%\postgres_backup.log"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"`) do set "STAMP=%%T"
set "BACKUP_FILE=%BACKUP_DIR%\darkjutsu_backup_%STAMP%.backup"

echo ================================================== >> "%LOGFILE%"
echo [%date% %time%] Iniciando backup Dark-Jutsu... >> "%LOGFILE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-RestMethod -Uri '%API_URL%' -TimeoutSec 3; if ($r.ok -eq $true) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not %errorlevel%==0 (
    echo [%date% %time%] API local nao esta ativa. Backup ignorado; esta maquina nao e o servidor em uso. >> "%LOGFILE%"
    exit /b 0
)

if not exist "%PG_BIN%\pg_dump.exe" (
    echo [%date% %time%] ERRO: pg_dump.exe nao encontrado em %PG_BIN%. >> "%LOGFILE%"
    exit /b 1
)

"%PG_BIN%\pg_isready.exe" -h "%PGHOST%" -p "%PGPORT%" -U "%PGUSER%" -d "%PGDATABASE%" >nul 2>&1
if not %errorlevel%==0 (
    echo [%date% %time%] ERRO: PostgreSQL nao esta pronto em %PGHOST%:%PGPORT%. >> "%LOGFILE%"
    exit /b 1
)

"%PG_BIN%\pg_dump.exe" -h "%PGHOST%" -p "%PGPORT%" -U "%PGUSER%" -d "%PGDATABASE%" -F c -f "%BACKUP_FILE%" >> "%LOGFILE%" 2>&1
if not %errorlevel%==0 (
    echo [%date% %time%] ERRO: falha ao gerar backup. >> "%LOGFILE%"
    exit /b 1
)

echo [%date% %time%] Backup criado pela maquina ativa: %BACKUP_FILE% >> "%LOGFILE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%BACKUP_DIR%' -Filter 'darkjutsu_backup_*.backup' | Sort-Object LastWriteTime -Descending | Select-Object -Skip 72 | Remove-Item -Force" >> "%LOGFILE%" 2>&1

exit /b 0
