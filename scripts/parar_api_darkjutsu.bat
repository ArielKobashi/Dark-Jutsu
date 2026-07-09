@echo off
setlocal EnableExtensions

set "LOGDIR=C:\DarkJutsu\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
copy /Y NUL "%LOGDIR%\.write_test" >nul 2>&1
if not %errorlevel%==0 set "LOGDIR=%TEMP%\DarkJutsu\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
del "%LOGDIR%\.write_test" >nul 2>&1
set "LOGFILE=%LOGDIR%\servidor_guardiao.log"

echo Encerrando API Dark-Jutsu na porta 8765...
echo [%date% %time%] ACAO MANUAL/AUTOMATICA: encerrar API local. Usuario=%USERNAME% Maquina=%COMPUTERNAME% >> "%LOGFILE%"

for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":8765 .*LISTENING"') do (
    echo Encerrando PID %%P
    echo [%date% %time%] Encerrando PID %%P da API. >> "%LOGFILE%"
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
