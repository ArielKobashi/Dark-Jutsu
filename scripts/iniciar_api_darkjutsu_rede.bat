@echo off
setlocal EnableExtensions

set "DARK_JUTSU_ROOT=%USERPROFILE%\Desktop\Dark-Jutsu"
set "DARK_JUTSU_API_HOST=0.0.0.0"
set "POSTGRES_STARTER=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\iniciar_postgres_darkjutsu.bat"

netstat -ano -p tcp | findstr /R /C:":8765 .*LISTENING" >nul
if %errorlevel%==0 (
    echo API Dark-Jutsu ja esta rodando na porta 8765.
    exit /b 0
)

if not exist "%DARK_JUTSU_ROOT%\api\iniciar_api.bat" (
    echo ERRO: api\iniciar_api.bat nao encontrado em %DARK_JUTSU_ROOT%.
    exit /b 1
)

if exist "%POSTGRES_STARTER%" (
    call "%POSTGRES_STARTER%"
)

wscript.exe //B "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\iniciar_api_darkjutsu_service.vbs"
exit /b 0
