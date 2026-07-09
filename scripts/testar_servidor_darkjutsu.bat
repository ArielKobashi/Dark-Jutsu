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

echo RESUMO RAPIDO
powershell -NoProfile -ExecutionPolicy Bypass -Command "$status=@(); foreach($item in @(@('Principal','192.168.5.44'),@('Reserva','192.168.5.38'))) { $ok=$false; try { $r=Invoke-RestMethod -Uri ('http://' + $item[1] + ':8765/health') -TimeoutSec 3; $ok=($r.ok -eq $true) } catch {}; $status += [pscustomobject]@{Nome=$item[0];IP=$item[1];Online=$ok}; if($ok){ Write-Host ('ONLINE  ' + $item[0] + '  ' + $item[1]) } else { Write-Host ('OFFLINE ' + $item[0] + '  ' + $item[1]) } }; $online=@($status | Where-Object Online); Write-Host ''; if($online.Count -eq 0){ Write-Host 'SITUACAO: nenhum servidor Dark-Jutsu respondeu agora.'; Write-Host 'ACAO: aguarde ate 1 minuto para o guardiao iniciar, ou use Verificar/Iniciar agora.' } elseif($online.Count -eq 1){ Write-Host ('SITUACAO: servidor ativo em ' + $online[0].Nome + ' (' + $online[0].IP + ').'); Write-Host 'ACAO: normal. Os outros PCs devem usar esse servidor automaticamente pelo sistema.' } else { Write-Host 'SITUACAO: ATENCAO, principal e reserva responderam ao mesmo tempo.'; Write-Host 'ACAO: use Encerrar no servidor que deve ficar como reserva, depois rode este teste de novo.' }"
echo.
echo DETALHES
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
    echo AVISO: PostgreSQL local nao esta pronto.
    echo SIGNIFICA: este PC nao esta com o banco local ativo agora.
    echo ACAO: se este PC deveria ser o servidor, use "Verificar/Iniciar agora" ou "Tornar este PC o principal".
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
    echo AVISO: API local nao respondeu.
    echo SIGNIFICA: este PC nao esta servindo o Dark-Jutsu pela porta 8765 neste momento.
    echo ACAO: isso e normal se outro PC estiver como servidor. Se nenhum servidor estiver online, aguarde o guardiao ou use "Verificar/Iniciar agora".
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
        echo SIGNIFICA: outros computadores nao conseguem usar este PC como servidor agora.
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
echo.
echo LEITURA DO ICONE:
echo Verde = este PC esta servindo.
echo Vermelho = outro PC esta servindo.
echo Preto = nenhum servidor respondeu agora.
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
