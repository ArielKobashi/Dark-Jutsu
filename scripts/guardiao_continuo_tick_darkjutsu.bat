@echo off
setlocal EnableExtensions

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "PRIMARY_IP=192.168.5.44"
set "RESERVE_IP=192.168.5.38"
set "API_PORT=8765"
set "LOGDIR=C:\DarkJutsu\logs"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
copy /Y NUL "%LOGDIR%\.write_test" >nul 2>&1
if not %errorlevel%==0 set "LOGDIR=%TEMP%\DarkJutsu\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
del "%LOGDIR%\.write_test" >nul 2>&1
set "LOGFILE=%LOGDIR%\servidor_guardiao.log"

for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -in @('%PRIMARY_IP%','%RESERVE_IP%') } | Select-Object -First 1 -ExpandProperty IPAddress)"`) do set "LOCAL_IP=%%I"
if "%LOCAL_IP%"=="" exit /b 0

call :health "%PRIMARY_IP%"
set "PRIMARY_OK=%errorlevel%"
call :health "%RESERVE_IP%"
set "RESERVE_OK=%errorlevel%"

if "%PRIMARY_OK%"=="0" (
    if not "%LOCAL_IP%"=="%PRIMARY_IP%" call "%SHARE_ROOT%\scripts\parar_api_darkjutsu.bat" >nul 2>&1
    exit /b 0
)

if "%RESERVE_OK%"=="0" (
    if "%LOCAL_IP%"=="%PRIMARY_IP%" (
        echo [%date% %time%] Principal reassumindo da reserva. >> "%LOGFILE%"
        call "%SHARE_ROOT%\scripts\assumir_servidor_darkjutsu.bat" >> "%LOGFILE%" 2>&1
    )
    exit /b 0
)

echo [%date% %time%] Nenhum servidor ativo; %LOCAL_IP% vai iniciar. >> "%LOGFILE%"
call "%SHARE_ROOT%\scripts\assumir_servidor_darkjutsu.bat" >> "%LOGFILE%" 2>&1
exit /b %errorlevel%

:health
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-RestMethod -Uri 'http://%~1:%API_PORT%/health' -TimeoutSec 3; if ($r.ok -eq $true) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
exit /b %errorlevel%
