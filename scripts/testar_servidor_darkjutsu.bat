@echo off
setlocal EnableExtensions

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "PG_BIN=C:\DarkJutsu\PostgreSQL\pgsql\bin"
set "PGDATA=C:\DarkJutsu\postgres-data"
set "APP_ROOT=%USERPROFILE%\Desktop\Dark-Jutsu"
set "LOCAL_IP="

for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1 -ExpandProperty IPAddress)"`) do set "LOCAL_IP=%%I"

echo ==================================================
echo TESTE DARK-JUTSU SERVIDOR
echo Usuario: %USERNAME%
echo Maquina: %COMPUTERNAME%
echo IP local: %LOCAL_IP%
echo ==================================================
echo.

echo [1. Acesso ao servidor de arquivos]
if exist "%SHARE_ROOT%\app\index.html" (
    echo OK: app encontrado na rede.
) else (
    echo FALHOU: app nao encontrado na rede.
    goto fail
)

echo.
echo [2. Scripts compartilhados]
if exist "%SHARE_ROOT%\scripts\iniciar_postgres_darkjutsu.bat" (
    echo OK: scripts encontrados.
) else (
    echo FALHOU: scripts nao encontrados.
    goto fail
)

echo.
echo [3. PostgreSQL portable local]
if exist "%PG_BIN%\pg_ctl.exe" (
    echo OK: pg_ctl encontrado.
) else (
    echo FALHOU: pg_ctl nao encontrado.
    goto fail
)

echo.
echo [4. PGDATA local]
if exist "%PGDATA%\postgresql.conf" (
    echo OK: PGDATA encontrado.
) else (
    echo FALHOU: PGDATA nao inicializado.
    goto fail
)

echo.
echo [5. Status PostgreSQL local]
"%PG_BIN%\pg_isready.exe" -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu
if errorlevel 1 (
    echo AVISO: PostgreSQL local nao esta pronto. Use "Verificar/Iniciar agora" para o guardiao decidir se deve iniciar.
) else (
    echo OK: PostgreSQL local pronto.
)

echo.
echo [6. Porta PostgreSQL 5433]
netstat -ano -p tcp | findstr /R /C:":5433 .*LISTENING"
if errorlevel 1 (
    echo FALHOU: porta 5433 nao esta ouvindo.
    goto fail
)
echo OK: porta 5433 ativa.

echo.
echo [7. Conexao SQL local]
"%PG_BIN%\psql.exe" -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu -At -c "select current_database() || '|' || current_user;"
if errorlevel 1 (
    echo FALHOU: nao conectou no banco dark_jutsu.
    goto fail
)
echo OK: conexao SQL funcionando.

echo.
echo [8. API local 8765]
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:8765/health' -TimeoutSec 5 | ConvertTo-Json -Compress } catch { exit 1 }"
if errorlevel 1 (
    echo AVISO: API local nao respondeu. O teste nao inicia servidor para evitar duplicidade.
) else (
    echo OK: API local respondendo.
)

echo.
echo [9. API pela rede nesta maquina]
if "%LOCAL_IP%"=="" (
    echo AVISO: IP local nao detectado, pulei este teste.
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod -Uri 'http://%LOCAL_IP%:8765/health' -TimeoutSec 5 | ConvertTo-Json -Compress } catch { exit 1 }"
    if errorlevel 1 (
        echo AVISO: API nao respondeu pelo IP %LOCAL_IP%.
    ) else (
        echo OK: API respondendo em http://%LOCAL_IP%:8765/health
    )
)

echo.
echo [9b. APIs principal e reserva]
powershell -NoProfile -ExecutionPolicy Bypass -Command "foreach ($ip in @('192.168.5.44','192.168.5.38')) { try { $r=Invoke-RestMethod -Uri ('http://' + $ip + ':8765/health') -TimeoutSec 5; if ($r.ok -eq $true) { Write-Host ('OK: ' + $ip + ' ativo') } else { Write-Host ('OFF: ' + $ip) } } catch { Write-Host ('OFF: ' + $ip) } }"

echo.
echo [10. Backup mais recente na rede]
powershell -NoProfile -ExecutionPolicy Bypass -Command "$b=Get-ChildItem -Path '%SHARE_ROOT%\backups' -Filter 'darkjutsu_backup_*.backup' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if ($b) { Write-Host ('OK: ' + $b.Name + ' - ' + $b.LastWriteTime) } else { Write-Host 'AVISO: nenhum backup encontrado'; exit 2 }"
if errorlevel 1 (
    echo AVISO: backup nao encontrado ou nao acessivel.
)

echo.
echo ==================================================
echo RESULTADO: OK
echo Sistema: %SHARE_ROOT%\app\index.html
echo API local: http://127.0.0.1:8765/health
if not "%LOCAL_IP%"=="" echo API rede: http://%LOCAL_IP%:8765/health
echo ==================================================
pause
exit /b 0

:fail
echo.
echo ==================================================
echo RESULTADO: FALHOU
echo Leia a etapa acima que marcou erro.
echo ==================================================
pause
exit /b 1
