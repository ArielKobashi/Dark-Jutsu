@echo off
setlocal EnableExtensions

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "LOGDIR=C:\DarkJutsu\logs"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
copy /Y NUL "%LOGDIR%\.write_test" >nul 2>&1
if not %errorlevel%==0 set "LOGDIR=%TEMP%\DarkJutsu\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
del "%LOGDIR%\.write_test" >nul 2>&1
set "LOGFILE=%LOGDIR%\servidor_guardiao.log"

echo ================================================== >> "%LOGFILE%"
echo [%date% %time%] Solicitado: tornar esta maquina o servidor Dark-Jutsu. >> "%LOGFILE%"

call "%SHARE_ROOT%\scripts\iniciar_postgres_darkjutsu.bat" >> "%LOGFILE%" 2>&1
if errorlevel 1 exit /b 1

wscript.exe //B "%SHARE_ROOT%\scripts\iniciar_api_darkjutsu_hidden.vbs"
exit /b 0
