@echo off
setlocal EnableExtensions

set "SCRIPT_UNC=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\iniciar_servidor_se_necessario_darkjutsu.vbs"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_NAME=Guardiao Servidor Dark-Jutsu.lnk"
set "SHORTCUT_PATH=%STARTUP%\%SHORTCUT_NAME%"

if not exist "%SCRIPT_UNC%" (
    echo ERRO: script nao encontrado em:
    echo %SCRIPT_UNC%
    exit /b 1
)

del "%STARTUP%\Iniciar PostgreSQL Dark-Jutsu.lnk" >nul 2>&1
del "%STARTUP%\Iniciar API Dark-Jutsu.lnk" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath='wscript.exe'; $s.Arguments='//B ""%SCRIPT_UNC%""'; $s.WorkingDirectory='\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts'; $s.WindowStyle=7; $s.Save()"

if %errorlevel%==0 (
    echo Atalho guardiao criado em:
    echo %SHORTCUT_PATH%
    echo.
    echo Atalhos antigos de PostgreSQL/API foram removidos deste usuario.
    exit /b 0
)

echo ERRO: nao foi possivel criar o atalho guardiao.
exit /b 1
