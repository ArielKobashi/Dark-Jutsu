@echo off
setlocal EnableExtensions

echo Encerrando API Dark-Jutsu na porta 8765...

for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":8765 .*LISTENING"') do (
    echo Encerrando PID %%P
    taskkill /PID %%P /F
)

echo Verificando porta 8765...
netstat -ano -p tcp | findstr /R /C:":8765 .*LISTENING" >nul
if %errorlevel%==0 (
    echo ERRO: API ainda esta ouvindo na porta 8765.
    exit /b 1
)

echo API parada ou nao estava ativa.
exit /b 0
