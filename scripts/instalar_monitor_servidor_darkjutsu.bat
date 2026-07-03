@echo off
setlocal EnableExtensions

set "SCRIPT_UNC=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\monitor_servidor_darkjutsu_hidden.vbs"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_NAME=Monitor Servidor Dark-Jutsu.lnk"
set "SHORTCUT_PATH=%STARTUP%\%SHORTCUT_NAME%"

if not exist "%SCRIPT_UNC%" (
    echo ERRO: script nao encontrado em:
    echo %SCRIPT_UNC%
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath='wscript.exe'; $s.Arguments='//B ""%SCRIPT_UNC%""'; $s.WorkingDirectory='\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts'; $s.WindowStyle=7; $s.Save()"

if %errorlevel%==0 (
    echo Atalho do monitor criado em:
    echo %SHORTCUT_PATH%
    echo.
    echo Iniciando monitor agora...
    wscript.exe //B "%SCRIPT_UNC%"
    exit /b 0
)

echo ERRO: nao foi possivel criar o atalho do monitor.
exit /b 1
