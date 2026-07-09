@echo off
setlocal EnableExtensions

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "PAUSE_FILE=%SHARE_ROOT%\principal-pausado-ate.txt"
set "LOGDIR=C:\DarkJutsu\logs"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
copy /Y NUL "%LOGDIR%\.write_test" >nul 2>&1
if not %errorlevel%==0 set "LOGDIR=%TEMP%\DarkJutsu\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
del "%LOGDIR%\.write_test" >nul 2>&1
set "LOGFILE=%LOGDIR%\servidor_guardiao.log"

echo ================================================== >> "%LOGFILE%"
echo [%date% %time%] ACAO MANUAL: tornar esta maquina principal operacional. Usuario=%USERNAME% Maquina=%COMPUTERNAME% >> "%LOGFILE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Date).AddMinutes(10).ToString('o') | Set-Content -LiteralPath '%PAUSE_FILE%' -Encoding ASCII" >nul 2>&1
echo [%date% %time%] Principal fixa pausada por ate 10 minutos para esta maquina assumir. >> "%LOGFILE%"

call "%SHARE_ROOT%\scripts\assumir_servidor_darkjutsu.bat" >> "%LOGFILE%" 2>&1
exit /b %errorlevel%
