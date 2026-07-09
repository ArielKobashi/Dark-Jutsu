@echo off
setlocal EnableExtensions

set "SCRIPT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\guardiao_continuo_tick_darkjutsu_hidden.vbs"
set "TASK_NAME=Dark-Jutsu Guardiao Servidor"

if not exist "%SCRIPT%" (
    echo ERRO: script nao encontrado em:
    echo %SCRIPT%
    exit /b 1
)

schtasks /Delete /F /TN "%TASK_NAME%" >nul 2>&1
schtasks /Create /F /TN "%TASK_NAME%" /SC MINUTE /MO 1 /TR "wscript.exe //B \"%SCRIPT%\"" >nul 2>&1
schtasks /Change /TN "%TASK_NAME%" /RI 1 /DU 9999:59 >nul 2>&1
if %errorlevel%==0 (
    echo Guardiao continuo instalado: verifica servidor a cada 1 minuto.
    exit /b 0
)

echo AVISO: nao foi possivel criar tarefa agendada do guardiao.
echo Criando fallback no Inicializar do usuario.

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP%\Guardiao Continuo Dark-Jutsu.lnk"
set "FALLBACK_CMD=%STARTUP%\Guardiao Continuo Dark-Jutsu.cmd"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath='wscript.exe'; $s.Arguments='//B ""%SCRIPT%""'; $s.WorkingDirectory='\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts'; $s.WindowStyle=7; $s.Save()" >nul 2>nul
if exist "%SHORTCUT_PATH%" (
    echo Fallback criado no Inicializar:
    echo %SHORTCUT_PATH%
    exit /b 0
)

echo AVISO: nao foi possivel criar atalho .lnk do guardiao.
echo Criando fallback .cmd no Inicializar.
(
    echo @echo off
    echo wscript.exe //B "%SCRIPT%"
) > "%FALLBACK_CMD%" 2>nul

if exist "%FALLBACK_CMD%" (
    echo Fallback criado no Inicializar:
    echo %FALLBACK_CMD%
    exit /b 0
)

echo ERRO: nao foi possivel criar fallback do guardiao.
echo Abra o Inicializar com: explorer shell:startup
echo E crie manualmente um .cmd com:
echo wscript.exe //B "%SCRIPT%"
exit /b 1
