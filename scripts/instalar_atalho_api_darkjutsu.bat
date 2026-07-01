@echo off
setlocal EnableExtensions

set "SCRIPT_UNC=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\iniciar_api_darkjutsu.bat"
set "SHORTCUT_NAME=Iniciar API Dark-Jutsu.lnk"
set "SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\%SHORTCUT_NAME%"

if not exist "%SCRIPT_UNC%" (
    echo ERRO: script nao encontrado em:
    echo %SCRIPT_UNC%
    echo.
    echo Copie os scripts deste projeto para a pasta de rede antes de instalar o atalho.
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath='%SCRIPT_UNC%'; $s.WorkingDirectory='\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts'; $s.WindowStyle=7; $s.Save()"

if %errorlevel%==0 (
    echo Atalho criado em:
    echo %SHORTCUT_PATH%
    exit /b 0
)

echo ERRO: nao foi possivel criar o atalho.
exit /b 1
