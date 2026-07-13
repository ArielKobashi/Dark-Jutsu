@echo off
setlocal EnableExtensions

set "LOGDIR=C:\DarkJutsu\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
copy /Y NUL "%LOGDIR%\.write_test" >nul 2>&1
if not %errorlevel%==0 set "LOGDIR=%TEMP%\DarkJutsu\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
del "%LOGDIR%\.write_test" >nul 2>&1
set "LOGFILE=%LOGDIR%\servidor_guardiao.log"
set "CALLER=%~1"

echo Encerrando API Dark-Jutsu na porta 8765...
echo [%date% %time%] ACAO MANUAL/AUTOMATICA: encerrar API local. Usuario=%USERNAME% Maquina=%COMPUTERNAME% Caller=%CALLER% >> "%LOGFILE%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$log='%LOGFILE%'; $me=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $PID); $parent=$null; if($me){$parent=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $me.ParentProcessId)}; $line=('[{0}] PARAR_API_DETALHE powershell_pid={1} parent_pid={2} parent_name={3} parent_cmd={4}' -f (Get-Date).ToString('dd/MM/yyyy HH:mm:ss.fff'), $PID, $me.ParentProcessId, $parent.Name, $parent.CommandLine); for($i=0;$i -lt 8;$i++){ try { Add-Content -LiteralPath $log -Encoding UTF8 -Value $line; break } catch { Start-Sleep -Milliseconds 150 } }"

for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":8765 .*LISTENING"') do (
    echo Encerrando PID %%P
    echo [%date% %time%] Encerrando PID %%P da API. >> "%LOGFILE%"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$log='%LOGFILE%'; $p=Get-CimInstance Win32_Process -Filter 'ProcessId=%%P'; $line=('[{0}] PARAR_API_ALVO pid=%%P name={1} cmd={2}' -f (Get-Date).ToString('dd/MM/yyyy HH:mm:ss.fff'), $p.Name, $p.CommandLine); for($i=0;$i -lt 8;$i++){ try { Add-Content -LiteralPath $log -Encoding UTF8 -Value $line; break } catch { Start-Sleep -Milliseconds 150 } }"
    taskkill /PID %%P /F
)

echo Verificando porta 8765...
netstat -ano -p tcp | findstr /R /C:":8765 .*LISTENING" >nul
if %errorlevel%==0 (
    echo ERRO: API ainda esta ouvindo na porta 8765.
    echo [%date% %time%] ERRO: API ainda esta ouvindo na porta 8765. >> "%LOGFILE%"
    exit /b 1
)

echo API parada ou nao estava ativa.
echo [%date% %time%] OK: API parada ou nao estava ativa. >> "%LOGFILE%"
exit /b 0
